from django.db import transaction
from rest_framework import serializers

from .models import Event, Reservation


class EventSerializer(serializers.ModelSerializer):
    reservations_count = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'title', 'venue', 'date', 'total_seats', 'available_seats',
            'status', 'created_at', 'reservations_count',
        ]
        read_only_fields = ['id', 'created_at', 'reservations_count']

    def get_reservations_count(self, obj):
        # Viewsets annotate this value to avoid one extra query per event.
        if hasattr(obj, 'confirmed_reservations_count'):
            return obj.confirmed_reservations_count
        return obj.reservations.filter(status='confirmed').count()

    def validate(self, data):
        total_seats = data.get('total_seats', getattr(self.instance, 'total_seats', 0))
        available_seats = data.get('available_seats', getattr(self.instance, 'available_seats', 0))
        if available_seats > total_seats:
            raise serializers.ValidationError('available_seats cannot exceed total_seats.')
        return data


class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = [
            'id', 'event', 'attendee_name', 'attendee_email',
            'seats_reserved', 'status', 'created_at',
        ]
        read_only_fields = ['id', 'status', 'created_at']

    def validate_seats_reserved(self, value):
        if value < 1:
            raise serializers.ValidationError('Must reserve at least 1 seat.')
        return value

    def validate(self, data):
        event = data.get('event', getattr(self.instance, 'event', None))
        seats_reserved = data.get('seats_reserved', getattr(self.instance, 'seats_reserved', 0))
        if event is None:
            return data

        if event.status not in ('upcoming', 'ongoing'):
            raise serializers.ValidationError(f'Cannot reserve seats for a {event.status} event.')

        available_seats = event.available_seats
        if self.instance and self.instance.status == 'confirmed' and self.instance.event_id == event.pk:
            available_seats += self.instance.seats_reserved
        if seats_reserved > available_seats:
            raise serializers.ValidationError(f'Only {available_seats} seat(s) available.')
        return data

    @transaction.atomic
    def create(self, validated_data):
        # Re-check under a row lock; serializer validation alone can race with another request.
        event = Event.objects.select_for_update().get(pk=validated_data['event'].pk)
        seats_reserved = validated_data['seats_reserved']
        if event.status not in ('upcoming', 'ongoing'):
            raise serializers.ValidationError(f'Cannot reserve seats for a {event.status} event.')
        if seats_reserved > event.available_seats:
            raise serializers.ValidationError(f'Only {event.available_seats} seat(s) available.')
        event.available_seats -= seats_reserved
        event.save(update_fields=['available_seats'])
        validated_data['event'] = event
        return Reservation.objects.create(**validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        # Lock the reservation first so cancellation and edits cannot both adjust seats.
        reservation = Reservation.objects.select_for_update().select_related('event').get(pk=instance.pk)
        if reservation.status != 'confirmed':
            raise serializers.ValidationError('Cancelled reservations cannot be edited.')

        requested_event = validated_data.get('event', reservation.event)
        requested_seats = validated_data.get('seats_reserved', reservation.seats_reserved)
        event_ids = sorted({reservation.event_id, requested_event.pk})
        locked_events = {
            event.pk: event
            for event in Event.objects.select_for_update().filter(pk__in=event_ids).order_by('pk')
        }
        old_event = locked_events[reservation.event_id]
        new_event = locked_events[requested_event.pk]

        if new_event.status not in ('upcoming', 'ongoing'):
            raise serializers.ValidationError(f'Cannot reserve seats for a {new_event.status} event.')

        if old_event.pk == new_event.pk:
            available_after_release = old_event.available_seats + reservation.seats_reserved
            if requested_seats > available_after_release:
                raise serializers.ValidationError(f'Only {available_after_release} seat(s) available.')
            new_event.available_seats = available_after_release - requested_seats
            new_event.save(update_fields=['available_seats'])
        else:
            if requested_seats > new_event.available_seats:
                raise serializers.ValidationError(f'Only {new_event.available_seats} seat(s) available.')
            old_event.available_seats += reservation.seats_reserved
            new_event.available_seats -= requested_seats
            old_event.save(update_fields=['available_seats'])
            new_event.save(update_fields=['available_seats'])

        for field, value in validated_data.items():
            setattr(reservation, field, new_event if field == 'event' else value)
        reservation.save()
        return reservation
