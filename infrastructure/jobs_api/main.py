from aws_cdk import (
    ArnFormat,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk.aws_apigateway import (
    AuthorizationType,
    AwsIntegration,
    EndpointType,
    IntegrationOptions,
    IntegrationResponse,
    JsonSchema,
    JsonSchemaType,
    JsonSchemaVersion,
    LogGroupLogDestination,
    MethodResponse,
    Model,
    PassthroughBehavior,
    RequestValidatorOptions,
    RestApi,
    StageOptions,
)
from aws_cdk.aws_dynamodb import (
    Table,
)
from aws_cdk.aws_iam import (
    AccountPrincipal,
    Effect,
    Policy,
    PolicyStatement,
    Role,
    ServicePrincipal,
)
from aws_cdk.aws_kms import (
    Key,
)
from aws_cdk.aws_logs import (
    LogGroup,
    RetentionDays,
)
from aws_cdk.aws_sqs import (
    IQueue,
)
from constructs import (
    Construct,
)
from json import (
    dumps,
)
from os import (
    getenv,
)


class JobsApiConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        pending_window: int = 7,
        removal_policy: RemovalPolicy = RemovalPolicy.DESTROY,
        retention: RetentionDays = RetentionDays.ONE_MONTH,
        stage_name: str = "dev",
    ) -> None:
        super().__init__(
            scope,
            construct_id,
        )

        self.__jobs_api_access_log_group_name = \
            "/aws/apigateway/JobsAPIAccessLogs"
        self.__jobs_api_access_log_key = Key(
            self,
            "JobsAPIAccessLogsKey",
            alias="alias/JobsAPIAccessLogsKey",
            enable_key_rotation=True,
            pending_window=Duration.days(pending_window),
            removal_policy=removal_policy,
        )
        self.__jobs_api_access_log_group = LogGroup(
            self,
            "JobsAPIAccessLogGroup",
            encryption_key=self.__jobs_api_access_log_key,
            log_group_name=self.
            __jobs_api_access_log_group_name,
            retention=retention,
        )
        self.__jobs_api = RestApi(
            self,
            "JobsAPI",
            description="Jobs API",
            deploy_options=StageOptions(
                access_log_destination=LogGroupLogDestination(
                    self.__jobs_api_access_log_group,
                ),
                stage_name=stage_name,
                tracing_enabled=True,
            ),
            endpoint_types=[
                EndpointType.REGIONAL,
            ],
        )
        self.__jobs_api_invoke_role_policy = Policy(
            self,
            "JobsAPIInvokeRolePolicy",
        )
        self.__jobs_request_model = Model(
            self,
            "JobsRequestModel",
            content_type="application/json",
            description="Model for requests to /jobs",
            model_name="JobsRequest",
            rest_api=self.__jobs_api,
            schema=JsonSchema(
                properties={
                    "seconds": JsonSchema(
                        minimum=1,
                        type=JsonSchemaType.INTEGER,
                    ),
                },
                schema=JsonSchemaVersion.DRAFT4,
                title="Jobs Request Schema",
                type=JsonSchemaType.OBJECT,
            ),
        )
        self.__jobs_resource = self.__jobs_api.root.add_resource("jobs")
        self.__job_id_resource = self.__jobs_resource.add_resource("{jobId}")
        self.__passthrough_behavior = PassthroughBehavior.WHEN_NO_TEMPLATES
        self.jobs_api_execution_role = Role(
            self,
            "JobsAPIExecutionRole",
            assumed_by=ServicePrincipal("apigateway.amazonaws.com"),
        )
        self.jobs_api_invoke_role = Role(
            self,
            "JobsAPIInvokeRole",
            assumed_by=AccountPrincipal(Stack.of(self).account),
        )

        self.__jobs_api.deployment_stage.node.default_child.add_metadata(
            "checkov",
            {
                "skip": [
                    {
                        "comment": ("API Gateway caching "
                                    "is not required"),
                        "id": "CKV_AWS_120",
                    },
                ],
            },
        )
        self.__jobs_api_invoke_role_policy.attach_to_role(
            self.jobs_api_invoke_role,
        )

    def add_job_id_method(
        self,
        jobs_table: Table,
    ) -> None:
        __job_id_method = self.__job_id_resource.add_method(
            "GET",
            authorization_type=AuthorizationType.IAM,
            integration=AwsIntegration(
                action="GetItem",
                options=IntegrationOptions(
                    credentials_role=self.jobs_api_execution_role,
                    passthrough_behavior=self.__passthrough_behavior,
                    integration_responses=[
                        IntegrationResponse(
                            response_templates={
                                "application/json": "\n".join([
                                    ("#set($inputRoot = "
                                     "$input.path('$').Item)"),
                                    "{",
                                    "  #if($inputRoot.parameters != $null)",
                                    ("  \"parameters\": "
                                     "$inputRoot.parameters.S,"),
                                    "  #end",
                                    "  #if($inputRoot.results != $null)",
                                    ("  \"results\": "
                                     "$inputRoot.results.S,"),
                                    "  #end",
                                    ("  \"status\": "
                                     "\"$inputRoot.status.S\""),
                                    "}",
                                ]),
                            },
                            status_code="200",
                        ),
                    ],
                    request_templates={
                        "application/json": dumps({
                            "Key": {
                                "id": {
                                    "S": "$input.params('jobId')",
                                },
                            },
                            "TableName": jobs_table.table_name,
                        }),
                    }),
                service="dynamodb",
            ),
            method_responses=[
                MethodResponse(
                    response_models={
                        "application/json": Model.EMPTY_MODEL,
                    },
                    response_parameters={
                        "method.response.header.Content-Type": True,
                    },
                    status_code="200",
                ),
            ],
        )

        self.__jobs_api_access_log_key.grant_encrypt_decrypt(
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
                            __jobs_api_access_log_group_name,
                            service="logs",
                        ),
                    },
                },
            ),
        )
        self.__jobs_api_invoke_role_policy.add_statements(
            PolicyStatement(
                actions=[
                    "execute-api:Invoke",
                ],
                effect=Effect.ALLOW,
                resources=[
                    __job_id_method.method_arn,
                ],
            ),
        )

    def add_jobs_method(
        self,
        jobs_queue: IQueue,
    ) -> None:
        __jobs_method = self.__jobs_resource.add_method(
            "POST",
            authorization_type=AuthorizationType.IAM,
            integration=AwsIntegration(
                options=IntegrationOptions(
                    credentials_role=self.jobs_api_execution_role,
                    integration_responses=[
                        IntegrationResponse(
                            response_templates={
                                "application/json": dumps({
                                    "id": "$context.requestId",
                                }),
                            },
                            status_code="200",
                        )
                    ],
                    passthrough_behavior=self.__passthrough_behavior,
                    request_parameters={
                        "integration.request.header.Content-Type":
                        "'application/x-www-form-urlencoded'",
                    },
                    request_templates={
                        "application/json":
                        ("Action="
                         "SendMessage&MessageBody="
                         "$input.json('$')&"
                         "MessageAttribute.1.Name="
                         "id&"
                         "MessageAttribute.1.Value.StringValue="
                         "$context.requestId&"
                         "MessageAttribute.1.Value.DataType=String"),
                    },
                ),
                path=(f"{getenv('CDK_DEFAULT_ACCOUNT')}"
                      f"/{jobs_queue.queue_name}"),
                proxy=False,
                service="sqs",
            ),
            request_models={
                "application/json": self.__jobs_request_model,
            },
            request_validator_options=RequestValidatorOptions(
                validate_request_body=True,
                validate_request_parameters=False,
            ),
        )

        __jobs_method.add_method_response(
            response_models={
                "application/json": Model.EMPTY_MODEL,
            },
            response_parameters={
                "method.response.header.Content-Type": True,
            },
            status_code="200",
        )
        self.__jobs_api_invoke_role_policy.add_statements(
            PolicyStatement(
                actions=[
                    "execute-api:Invoke",
                ],
                effect=Effect.ALLOW,
                resources=[
                    __jobs_method.method_arn,
                ],
            ),
        )
