"""
Integration Stack — ERP integration layer with SQS FIFO, DLQ, and translation Lambda.
"""

from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_lambda_event_sources as event_sources,
    aws_events as events,
    aws_sqs as sqs,
    aws_iam as iam,
    Duration,
)
from constructs import Construct


class IntegrationStack(Stack):
    """Deploys the ERP integration layer: consumes decisions, translates, executes."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        event_bus: events.IEventBus,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # DLQ for failed ERP integrations
        dlq = sqs.Queue(
            self,
            "ERPIntegrationDLQ",
            queue_name="erp-decision-dlq.fifo",
            fifo=True,
            retention_period=Duration.days(14),
        )

        # Reference the FIFO queue created in AgentComputeStack
        erp_queue = sqs.Queue.from_queue_arn(
            self,
            "ERPDecisionQueueRef",
            queue_arn=f"arn:aws:sqs:{self.region}:{self.account}:erp-decision-queue.fifo",
        )

        # Integration Lambda — translates agent decisions to ERP transactions
        integration_role = iam.Role(
            self,
            "ERPIntegrationRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # Secrets access for ERP credentials
        integration_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:erp/*"],
            )
        )

        # EventBridge publish for confirmation events
        integration_role.add_to_policy(
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[event_bus.event_bus_arn],
            )
        )

        # DLQ send
        integration_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sqs:SendMessage"],
                resources=[dlq.queue_arn],
            )
        )

        integration_fn = _lambda.Function(
            self,
            "ERPIntegrationFunction",
            function_name="sc-erp-integration",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("../lambdas/erp_integration"),
            memory_size=256,
            timeout=Duration.seconds(30),
            role=integration_role,
            environment={
                "EVENT_BUS_NAME": event_bus.event_bus_name,
                "DLQ_URL": dlq.queue_url,
                "ERP_SECRET_NAME": "erp/api-credentials",
            },
            retry_attempts=2,
            dead_letter_queue=dlq,
        )

        # Trigger from FIFO queue
        integration_fn.add_event_source(
            event_sources.SqsEventSource(
                erp_queue,
                batch_size=1,  # Process one decision at a time for ERP rate limiting
                max_batching_window=Duration.seconds(5),
            )
        )
