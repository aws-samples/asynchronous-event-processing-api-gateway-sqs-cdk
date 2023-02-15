from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
)
from aws_cdk.aws_logs import (
    RetentionDays,
)
from constructs import (
    Construct,
)
from infrastructure.event_processing.main import (
    EventProcessingConstruct,
)
from infrastructure.jobs_api.main import (
    JobsApiConstruct,
)


class InfrastructureStack(Stack):
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
        stage_name: str = "dev",
        write_capacity: int = 5,
        **kwargs,
    ) -> None:
        super().__init__(
            scope,
            construct_id,
            **kwargs,
        )

        self.__event_processing = EventProcessingConstruct(
            self,
            "EventProcessing",
            error_handling_timeout=error_handling_timeout,
            event_processing_timeout=event_processing_timeout,
            max_event_age=max_event_age,
            max_service_capacity=max_service_capacity,
            min_service_capacity=min_service_capacity,
            pending_window=pending_window,
            read_capacity=read_capacity,
            removal_policy=removal_policy,
            reserved_concurrent_executions=reserved_concurrent_executions,
            retention=retention,
            retry_attempts=retry_attempts,
            write_capacity=write_capacity,
        )
        self.__jobs_api = JobsApiConstruct(
            self,
            "JobsApi",
            pending_window=pending_window,
            removal_policy=removal_policy,
            retention=retention,
            stage_name=stage_name,
        )

        CfnOutput(
            self,
            "JobsAPIInvokeRole",
            value=self.__jobs_api.jobs_api_invoke_role.role_arn,
        )
        self.__event_processing.jobs_queue.grant_send_messages(
            self.__jobs_api.jobs_api_execution_role)
        self.__event_processing.jobs_table.grant_read_data(
            self.__jobs_api.jobs_api_execution_role)
        self.__jobs_api.add_job_id_method(
            jobs_table=self.__event_processing.jobs_table)
        self.__jobs_api.add_jobs_method(
            jobs_queue=self.
            __event_processing.
            jobs_queue)
        self.add_metadata(
            "cfn-lint", {
                "config": {
                    "ignore_checks": [
                        "W3005",
                    ],
                },
            },
        )
