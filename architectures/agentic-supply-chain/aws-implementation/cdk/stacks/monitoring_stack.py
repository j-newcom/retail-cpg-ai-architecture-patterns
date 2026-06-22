"""
Monitoring Stack — CloudWatch dashboards, alarms, and anomaly detection.
"""

from aws_cdk import (
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_lambda as _lambda,
    Duration,
)
from constructs import Construct


class MonitoringStack(Stack):
    """Deploys monitoring dashboards and critical alarms for the agent network."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        agent_functions: list[_lambda.Function],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Alert topic
        alert_topic = sns.Topic(
            self,
            "AgentAlertTopic",
            topic_name="supply-chain-agent-alerts",
            display_name="Supply Chain Agent Alerts",
        )

        # Dashboard
        dashboard = cloudwatch.Dashboard(
            self,
            "AgentDashboard",
            dashboard_name="SupplyChainAgents",
        )

        # Per-agent widgets
        for fn in agent_functions:
            dashboard.add_widgets(
                cloudwatch.GraphWidget(
                    title=f"{fn.function_name} — Invocations & Errors",
                    left=[
                        fn.metric_invocations(period=Duration.minutes(5)),
                    ],
                    right=[
                        fn.metric_errors(period=Duration.minutes(5)),
                    ],
                    width=12,
                ),
                cloudwatch.GraphWidget(
                    title=f"{fn.function_name} — Duration",
                    left=[
                        fn.metric_duration(period=Duration.minutes(5)),
                    ],
                    width=12,
                ),
            )

            # Error rate alarm per agent
            error_alarm = cloudwatch.Alarm(
                self,
                f"ErrorAlarm-{fn.function_name}",
                metric=fn.metric_errors(period=Duration.minutes(5)),
                threshold=3,
                evaluation_periods=2,
                alarm_description=f"Agent {fn.function_name} error rate elevated",
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            error_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # Custom metric widgets — business-level monitoring
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Decisions per Hour (All Agents)",
                left=[
                    cloudwatch.Metric(
                        namespace="SupplyChainAgents",
                        metric_name="DecisionCount",
                        statistic="Sum",
                        period=Duration.hours(1),
                    )
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Escalation Rate",
                left=[
                    cloudwatch.Metric(
                        namespace="SupplyChainAgents",
                        metric_name="EscalationCount",
                        statistic="Sum",
                        period=Duration.hours(1),
                    )
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Average Confidence Score",
                left=[
                    cloudwatch.Metric(
                        namespace="SupplyChainAgents",
                        metric_name="ConfidenceScore",
                        statistic="Average",
                        period=Duration.hours(1),
                    )
                ],
                width=12,
            ),
            cloudwatch.GraphWidget(
                title="Autonomous Spend (USD)",
                left=[
                    cloudwatch.Metric(
                        namespace="SupplyChainAgents",
                        metric_name="AutonomousSpendUSD",
                        statistic="Sum",
                        period=Duration.hours(1),
                    )
                ],
                width=12,
            ),
        )

        # Circuit breaker alarm — total decisions exceeding threshold
        cloudwatch.Alarm(
            self,
            "CircuitBreakerAlarm",
            metric=cloudwatch.Metric(
                namespace="SupplyChainAgents",
                metric_name="DecisionCount",
                statistic="Sum",
                period=Duration.hours(1),
            ),
            threshold=1000,
            evaluation_periods=1,
            alarm_description="Circuit breaker: decision volume exceeds 1000/hour",
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )
