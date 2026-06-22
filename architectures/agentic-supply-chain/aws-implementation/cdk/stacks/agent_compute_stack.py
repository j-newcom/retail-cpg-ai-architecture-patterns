"""
Agent Compute Stack — Lambda functions for each supply chain agent.
"""

from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_sqs as sqs,
    Duration,
)
from constructs import Construct


AGENTS = [
    {
        "name": "demand-sensing",
        "memory": 512,
        "timeout": 120,
        "events": ["POSDataRefresh", "SocialSignalUpdate", "WeatherForecastUpdate", "PromoCalendarChange"],
    },
    {
        "name": "inventory-allocation",
        "memory": 512,
        "timeout": 120,
        "events": ["DemandAdjustment", "InventoryLevelChange", "ShipmentETAUpdate"],
    },
    {
        "name": "procurement",
        "memory": 512,
        "timeout": 120,
        "events": ["InventoryDepletionForecast", "SupplierCapacityUpdate", "SupplierRiskAlert"],
    },
    {
        "name": "logistics",
        "memory": 512,
        "timeout": 120,
        "events": ["TransferOrder", "TrafficConditionUpdate", "PortCongestionAlert"],
    },
    {
        "name": "disruption-response",
        "memory": 1024,
        "timeout": 300,
        "events": ["DisruptionEvent", "SupplierRiskAlert", "QualityRecallNotice"],
    },
]


class AgentComputeStack(Stack):
    """Deploys Lambda functions for all 5 supply chain agents."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        event_bus: events.IEventBus,
        neptune_endpoint: str,
        opensearch_endpoint: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.agent_functions: list[_lambda.Function] = []

        # Shared escalation queue
        self.escalation_queue = sqs.Queue(
            self,
            "EscalationQueue",
            queue_name="escalation-queue",
            visibility_timeout=Duration.seconds(300),
        )

        # ERP decision queue (FIFO for ordering guarantees)
        self.erp_queue = sqs.Queue(
            self,
            "ERPDecisionQueue",
            queue_name="erp-decision-queue.fifo",
            fifo=True,
            content_based_deduplication=True,
            visibility_timeout=Duration.seconds(60),
        )

        # Create agent execution role
        agent_role = self._create_agent_role(event_bus)

        # Deploy each agent
        for agent_config in AGENTS:
            fn = self._create_agent_function(
                agent_config, event_bus, agent_role, neptune_endpoint, opensearch_endpoint
            )
            self.agent_functions.append(fn)

    def _create_agent_role(self, event_bus: events.IEventBus) -> iam.Role:
        """Create the shared IAM role for agent Lambda functions."""
        role = iam.Role(
            self,
            "AgentExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # Bedrock invoke
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-20250514",
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-20250514",
                ],
            )
        )

        # EventBridge publish
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["events:PutEvents"],
                resources=[event_bus.event_bus_arn],
            )
        )

        # SQS send (escalation + ERP queues)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["sqs:SendMessage", "sqs:GetQueueUrl"],
                resources=[
                    self.escalation_queue.queue_arn,
                    self.erp_queue.queue_arn,
                ],
            )
        )

        # CloudWatch custom metrics
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {"cloudwatch:namespace": "SupplyChainAgents"}
                },
            )
        )

        # S3 audit writes
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=["arn:aws:s3:::supply-chain-decisions/*"],
            )
        )

        return role

    def _create_agent_function(
        self,
        config: dict,
        event_bus: events.IEventBus,
        role: iam.Role,
        neptune_endpoint: str,
        opensearch_endpoint: str,
    ) -> _lambda.Function:
        """Create a Lambda function for a single agent."""
        fn = _lambda.Function(
            self,
            f"Agent-{config['name']}",
            function_name=f"sc-agent-{config['name']}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset(f"../lambdas/{config['name'].replace('-', '_')}"),
            memory_size=config["memory"],
            timeout=Duration.seconds(config["timeout"]),
            role=role,
            environment={
                "EVENT_BUS_NAME": event_bus.event_bus_name,
                "NEPTUNE_ENDPOINT": neptune_endpoint,
                "OPENSEARCH_ENDPOINT": opensearch_endpoint,
                "AGENT_NAME": config["name"],
                "MODEL_ID": "anthropic.claude-sonnet-4-20250514",
                "ESCALATION_QUEUE_URL": self.escalation_queue.queue_url,
                "ERP_QUEUE_URL": self.erp_queue.queue_url,
                "DECISION_LOG_BUCKET": "supply-chain-decisions",
            },
            reserved_concurrent_executions=10,  # Prevent runaway invocations
        )

        # Create EventBridge rule to trigger this agent
        for event_type in config["events"]:
            events.Rule(
                self,
                f"Rule-{config['name']}-{event_type}",
                event_bus=event_bus,
                event_pattern=events.EventPattern(
                    source=[{"prefix": "supply-chain"}],
                    detail_type=[event_type],
                ),
                targets=[targets.LambdaFunction(fn)],
            )

        return fn
