from aws_lambda_powertools.utilities.typing import (
    LambdaContext,
)
from botocore.stub import (
    Stubber,
)
from error_handling.main import (
    dynamodb,
    handler,
)
from json import (
    dumps,
)
from pytest import (
    fixture,
)
from tests.fixtures import (
    context,
)


@fixture
def dynamodb_stub(event: dict) -> Stubber:
    dynamodb_stub = Stubber(dynamodb)
    record = event["Records"][0]
    parameters = record["body"]

    dynamodb_stub.add_response(
        "put_item",
        expected_params={
            "Item": {
                "id": {
                    "S": "1",
                },
                "parameters": {
                    "S": dumps(parameters),
                },
                "status": {
                    "S": "Failure",
                },
            },
            "TableName": "jobs",
        },
        service_response=dict(),
    )

    yield dynamodb_stub


@fixture
def event() -> dict:
    event = {
        "Records": [
            {
                "body": {
                    "parameters": {
                        "seconds": 301,
                    },
                },
                "messageAttributes": {
                    "id": {
                        "stringValue": "1",
                    },
                },
            },
        ]
    }

    yield event


def test_error_handling(
    context: LambdaContext,
    dynamodb_stub: Stubber,
    event: dict,
) -> None:
    with dynamodb_stub:
        handler(event, context)
