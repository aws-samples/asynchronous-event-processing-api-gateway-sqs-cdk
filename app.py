from infrastructure.main import (
    InfrastructureStack,
)
from aws_cdk import (
    App,
)

app = App()

InfrastructureStack(
    app,
    "AsynchronousEventProcessingAPIGatewaySQS",
    description="Asynchronous Event Processing with API Gateway and SQS",
)

app.synth()
