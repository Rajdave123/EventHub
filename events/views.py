from django.db import transaction
from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Event, Reservation
from .serializers import EventSerializer, ReservationSerializer


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer

    def get_queryset(self):
        queryset = Event.objects.annotate(
            confirmed_reservations_count=Count(
                'reservations', filter=Q(reservations__status='confirmed'), distinct=True
            )
        )
        status_param = self.request.query_params.get('status')
        venue_param = self.request.query_params.get('venue')
        if status_param:
            queryset = queryset.filter(status=status_param)
        if venue_param:
            queryset = queryset.filter(venue__icontains=venue_param)
        return queryset


class ReservationViewSet(viewsets.ModelViewSet):
    serializer_class = ReservationSerializer

    def get_queryset(self):
        queryset = Reservation.objects.select_related('event').all()
        event_id = self.request.query_params.get('event_id')
        if event_id:
            queryset = queryset.filter(event_id=event_id)
        return queryset

    def perform_destroy(self, instance):
        # ModelViewSet exposes DELETE; keep event availability consistent on that path too.
        with transaction.atomic():
            reservation = Reservation.objects.select_for_update().get(pk=instance.pk)
            if reservation.status == 'confirmed':
                event = Event.objects.select_for_update().get(pk=reservation.event_id)
                event.available_seats += reservation.seats_reserved
                event.save(update_fields=['available_seats'])
            reservation.delete()

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        with transaction.atomic():
            reservation_id = self.get_object().pk
            reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
            if reservation.status == 'cancelled':
                return Response({'error': 'Already cancelled.'}, status=status.HTTP_400_BAD_REQUEST)

            event = Event.objects.select_for_update().get(pk=reservation.event_id)
            event.available_seats += reservation.seats_reserved
            event.save(update_fields=['available_seats'])
            reservation.status = 'cancelled'
            reservation.save(update_fields=['status'])

        return Response(self.get_serializer(reservation).data)
