"""Customer Service specific endpoint."""

import logging
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from .models.requests import QueryRequest, CustomerServiceRequest
from .utils.context_storage import save_context
from .dependencies import get_agent_service


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer-service", tags=["customer-service"])


@router.post("/query")
async def customer_service_query(request: CustomerServiceRequest):
    """
    Customer service agent endpoint.

    This endpoint wraps the generic agent service with customer-service specific
    configuration and metadata.
    """
    logger.info(
        f"Customer service request: tenant={request.tenant_id}, "
        f"service_type={request.service_type}, session={request.session_id}"
    )

    # Build metadata from business-specific fields
    metadata = {}
    if request.service_type:
        metadata["service_type"] = request.service_type
    if request.customer_id:
        metadata["customer_id"] = request.customer_id

    # Convert to generic QueryRequest
    generic_request = QueryRequest(
        tenant_id=request.tenant_id,
        prompt=request.prompt,
        skill="customer-service",  # Fixed skill for this endpoint
        language=request.language,
        session_id=request.session_id,
        context=request.context,
        metadata=metadata if metadata else None
    )

    # Save context if provided
    context_file_path = None
    if request.context:
        context_file_path = save_context(
            tenant_id=request.tenant_id,
            context=request.context
        )

    # Get service and process (dependency injection)
    agent_service = get_agent_service()

    return EventSourceResponse(
        agent_service.process_query(generic_request, context_file_path=context_file_path),
        media_type="text/event-stream"
    )
