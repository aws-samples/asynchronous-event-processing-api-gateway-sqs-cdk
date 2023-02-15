from aws_cdk import (
    ArnFormat,
    BundlingOptions,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk.aws_dynamodb import (
    Attribute,
    AttributeType,
    Table,
    TableEncryption,
)
from aws_cdk.aws_ec2 import (
    GatewayVpcEndpointAwsService,
)
from aws_cdk.aws_ecr_assets import (
    Platform,
)
from aws_cdk.aws_ecs import (
    AwsLogDriver,
    CapacityProviderStrategy,
    Cluster,
    ContainerImage,
)
from aws_cdk.aws_ecs_patterns import (
    QueueProcessingFargateService,
)
from aws_cdk.aws_events import (
    EventBus,
    EventPattern,
)
from aws_cdk.aws_iam import (
    AnyPrincipal,
    Effect,
    PolicyStatement,
    ServicePrincipal,
)
from aws_cdk.aws_kms import (
    Key,
)
from aws_cdk.aws_logs import (
    LogGroup,
    RetentionDays,
)
from aws_cdk.aws_lambda import (
    Code,
    Function,
    LayerVersion,
    Runtime,
)
from aws_cdk.aws_lambda_destinations import (
    EventBridgeDestination,
)
from aws_cdk.aws_lambda_event_sources import (
    SqsEventSource,
)
from aws_cdk.aws_sqs import (
    DeadLetterQueue,
    Queue,
    QueueEncryption,
)
from constructs import (
    Construct,
)
from pathlib import (
    Path,
)


class EventProcessingConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        error_handling_timeout: int = 300,
        event_processing_timeout: int = 300,
        max_event_age: int = 21600,
        max_service_capacity: int = 5,
        min_service_capacity: int = 1,
        pending_window: int = 7,
        read_capacity: int = 5,
        removal_policy: RemovalPolicy = RemovalPolicy.DESTROY,
        reserved_concurrent_executions: int = 100,
        retention: RetentionDays = RetentionDays.ONE_MONTH,
        retry_attempts: int = 0,
        write_capacity: int = 5,
    ) -> None:
        super().__init__(
            scope,
            construct_id,
        )

        self.__event_processing_cluster = Cluster(
            self,
            "EventProcessingCluster",
            container_insights=True,
        )
        self.__event_processing_image = ContainerImage.from_asset(
            str(
                Path(__file__).
                parent.
                parent.
                parent.
                joinpath("event_processing").
                resolve()
            ),
            platform=Platform.LINUX_AMD64,
        )
        self.__event_processing_service_log_group_name = \
            "/aws/ecs/EventProcessingServiceLogs"
        self.__event_processing_service_log_key = Key(
            self,
            "EventProcessingServiceLogsKey",
            alias="alias/EventProcessingServiceLogsKey",
            enable_key_rotation=True,
            pending_window=Duration.days(pending_window),
            removal_policy=removal_policy,
        )
        self.__event_processing_service_log_group = LogGroup(
            self,
            "EventProcessingServiceLogGroup",
            encryption_key=self.__event_processing_service_log_key,
            log_group_name=self.__event_processing_service_log_group_name,
            retention=retention,
        )
        self.__failed_jobs_event_bus = EventBus(
            self,
            "FailedJobsEventBus",
        )
        self.__jobs_queue_key = Key(
            self,
            "JobsQueueKey",
            alias="alias/JobsQueueKey",
            enable_key_rotation=True,
            pending_window=Duration.days(pending_window),
            removal_policy=removal_policy,
        )
        self.__failed_jobs_dead_letter_queue = Queue(
            self,
            "FailedJobsDeadLetterQueue",
            encryption=QueueEncryption.KMS,
            encryption_master_key=self.__jobs_queue_key,
            visibility_timeout=Duration.seconds(error_handling_timeout),
        )
        self.__jobs_table_key = Key(
            self,
            "JobsTableKey",
            alias="alias/JobsTableKey",
            enable_key_rotation=True,
            pending_window=Duration.days(pending_window),
            removal_policy=removal_policy,
        )
        self.__powertools_layer = LayerVersion(
            self,
            "PowertoolsLayer",
            code=Code.from_asset(
                str(
                    Path(__file__).
                    parent.
                    parent.
                    parent.
                    joinpath("powertools").
                    resolve()
                ),
                bundling=BundlingOptions(
                    command=[
                        "bash",
                        "-c",
                        ("mkdir /asset-output/python && "
                         "pip install "
                         "--requirement /asset-input/requirements.txt "
                         "--target /asset-output/python"),
                    ],
                    image=Runtime.PYTHON_3_9.bundling_image,
                ),
            ),
            compatible_runtimes=[
                Runtime.PYTHON_3_9,
            ],
            description="AWS Lambda Powertools for Python",
            license="MIT-0",
        )
        self.jobs_table = Table(
            self,
            "JobsTable",
            encryption=TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.__jobs_table_key,
            partition_key=Attribute(
                name="id",
                type=AttributeType.STRING,
            ),
            point_in_time_recovery=True,
            read_capacity=read_capacity,
            removal_policy=removal_policy,
            write_capacity=write_capacity,
        )
        self.__error_handling_function = Function(
            self,
            "ErrorHandlingFunction",
            code=Code.from_asset(
                str(
                    Path(__file__).
                    parent.
                    parent.
                    parent.
                    joinpath("error_handling").
                    resolve()
                ),
                bundling=BundlingOptions(
                    command=[
                        "bash",
                        "-c",
                        ("cp /asset-input/main.py "
                         "--target /asset-output "
                         "--update"),
                    ],
                    image=Runtime.PYTHON_3_9.bundling_image,
                ),
            ),
            environment={
                "TABLE_NAME": self.jobs_table.table_name,
                "QUEUE_NAME": self.
                __failed_jobs_dead_letter_queue.
                queue_name,
            },
            handler="main.handler",
            layers=[
                self.__powertools_layer,
            ],
            max_event_age=Duration.seconds(max_event_age),
            on_failure=EventBridgeDestination(self.__failed_jobs_event_bus),
            reserved_concurrent_executions=reserved_concurrent_executions,
            retry_attempts=retry_attempts,
            runtime=Runtime.PYTHON_3_9,
            timeout=Duration.seconds(error_handling_timeout),
        )
        self.jobs_queue = Queue(
            self,
            "JobsQueue",
            encryption=QueueEncryption.KMS,
            encryption_master_key=self.__jobs_queue_key,
            queue_name="jobs_queue",
            dead_letter_queue=DeadLetterQueue(
                max_receive_count=1,
                queue=self.__failed_jobs_dead_letter_queue,
            ),
            retention_period=Duration.seconds(max_event_age),
            visibility_timeout=Duration.seconds(event_processing_timeout),
        )
        self.__event_processing_service = QueueProcessingFargateService(
            self,
            "EventProcessingService",
            capacity_provider_strategies=[
                CapacityProviderStrategy(
                    capacity_provider="FARGATE",
                    weight=1,
                ),
                CapacityProviderStrategy(
                    capacity_provider="FARGATE_SPOT",
                    weight=2,
                ),
            ],
            cluster=self.__event_processing_cluster,
            enable_logging=True,
            environment={
                "QUEUE_NAME": self.jobs_queue.queue_name,
                "TABLE_NAME": self.jobs_table.table_name,
                "TIMEOUT": str(event_processing_timeout),
            },
            log_driver=AwsLogDriver.aws_logs(
                log_group=self.__event_processing_service_log_group,
                stream_prefix="event_processing",
            ),
            image=self.__event_processing_image,
            max_scaling_capacity=max_service_capacity,
            memory_limit_mib=1024,
            min_scaling_capacity=min_service_capacity,
            queue=self.jobs_queue,
        )
        self.__fargate_vpc = self.__event_processing_service.cluster.vpc
        self.__dynamo_db_gateway_endpoint = \
            self.__fargate_vpc.add_gateway_endpoint(
                "DynamoDBGatewayEndpoint",
                service=GatewayVpcEndpointAwsService.DYNAMODB,
            )

        self.__dynamo_db_gateway_endpoint.add_to_policy(
            PolicyStatement(
                actions=[
                    "dynamodb:PutItem",
                ],
                conditions={
                    "ArnEquals": {
                        "aws:PrincipalArn": self.
                        __event_processing_service.
                        task_definition.
                        task_role.
                        role_arn,
                    }
                },
                effect=Effect.ALLOW,
                principals=[
                    AnyPrincipal(),
                ],
                resources=[
                    self.jobs_table.table_arn,
                ],
            )
        )
        self.__error_handling_function.add_event_source(
            SqsEventSource(self.__failed_jobs_dead_letter_queue))
        self.__error_handling_function.node.default_child.add_metadata(
            "checkov",
            {
                "skip": [
                    {
                        "comment": ("This function uses "
                                    "Lambda Destinations"),
                        "id": "CKV_AWS_116",
                    },
                    {
                        "comment": ("This function is not meant "
                                    "to be run inside a VPC"),
                        "id": "CKV_AWS_117",
                    },
                    {
                        "comment": ("A customer managed key "
                                    "is not required"),
                        "id": "CKV_AWS_173",
                    },
                ],
            },
        )
        self.__event_processing_service.cluster.apply_removal_policy(
            removal_policy,
        )
        self.__event_processing_service_log_key.grant_encrypt_decrypt(
            ServicePrincipal(
                "logs.amazonaws.com",
                conditions={
                    "ArnEquals": {
                        "kms:EncryptionContext:aws:logs:arn":
                        Stack.of(self).format_arn(
                            arn_format=ArnFormat.
                            COLON_RESOURCE_NAME,
                            resource="log-group",
                            resource_name=self.
                            __event_processing_service_log_group_name,
                            service="logs",
                        ),
                    },
                },
            ),
        )
        self.__failed_jobs_event_bus.archive(
            "FailedJobsEventArchive",
            description="Failed Jobs Event Archive",
            event_pattern=EventPattern(),
        )
        self.jobs_queue.add_to_resource_policy(
            PolicyStatement(
                actions=[
                    "sqs:*",
                ],
                conditions={
                    "Bool": {
                        "aws:SecureTransport": "false",
                    },
                },
                effect=Effect.DENY,
                principals=[
                    AnyPrincipal(),
                ],
                resources=[
                    self.jobs_queue.queue_arn,
                ],
            )
        )
        self.jobs_table.grant_read_write_data(
            self.__error_handling_function,
        )
        self.jobs_table.grant_read_write_data(
            self.__event_processing_service.task_definition.task_role,
        )
