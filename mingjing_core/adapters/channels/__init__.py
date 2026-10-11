"""Thin identity, source and delivery adapters for the domain service.

Channels do not interpret model results or independently write facts. All
consultations, including scheduled reports, use ConsultationService.
"""
from .hermes import HermesChannelAdapter
from .reports import CoreReportAdapter, report_schedule
from .delivery import CoreDeliveryWorker, TransportRejected

__all__ = ["HermesChannelAdapter", "CoreReportAdapter", "report_schedule", "CoreDeliveryWorker", "TransportRejected"]
