"""
Reasoning Stack — Neptune Serverless + OpenSearch Serverless for agent context.
"""

from aws_cdk import (
    Stack,
    aws_neptune_alpha as neptune,
    aws_opensearchserverless as aoss,
    CfnOutput,
    RemovalPolicy,
)
from constructs import Construct


class ReasoningStack(Stack):
    """Deploys Neptune (knowledge graph) and OpenSearch (vector store)."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Neptune Serverless — supply chain knowledge graph
        self.neptune_cluster = neptune.DatabaseCluster(
            self,
            "SupplyChainGraph",
            vpc=None,  # Replace with VPC reference in production
            instance_type=neptune.InstanceType.SERVERLESS,
            serverless_scaling_configuration=neptune.ServerlessScalingConfiguration(
                min_capacity=1,
                max_capacity=8,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.neptune_endpoint = self.neptune_cluster.cluster_endpoint.hostname

        # OpenSearch Serverless — decision history vector search
        self.vector_collection = aoss.CfnCollection(
            self,
            "DecisionHistoryVectors",
            name="decision-history",
            type="VECTORSEARCH",
            description="Historical supply chain decisions for similarity retrieval",
        )

        self.opensearch_endpoint = self.vector_collection.attr_collection_endpoint

        # Outputs
        CfnOutput(self, "NeptuneEndpoint", value=self.neptune_endpoint)
        CfnOutput(self, "OpenSearchEndpoint", value=self.opensearch_endpoint)
