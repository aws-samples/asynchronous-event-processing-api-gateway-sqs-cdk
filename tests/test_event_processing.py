from botocore.stub import (
    Stubber,
)
from event_processing.main import (
    Event,
    Parameters,
    dynamodb,
    event_processing,
)
from os import (
    getenv,
)
from pytest import (
    fixture,
)


@fixture
def dynamodb_stub(event_success: Event) -> Stubber:
    dynamodb_stub = Stubber(dynamodb)
    parameters = event_success.Body
    seconds = parameters.seconds
    message = f"I slept for {seconds} seconds"

    dynamodb_stub.add_response(
        "put_item",
        expected_params={
            "Item": {
                "id": {
                    "S": "2",
                },
                "results": {
                    "S": f"{{\"message\": \"{message}\"}}",
                },
                "status": {
                    "S": "Success",
                },
            },
            "TableName": "jobs",
        },
        service_response=dict(),
    )

    yield dynamodb_stub


@fixture
def event_failure() -> Event:
    event_failure = Event(
        Body=Parameters(
            seconds=301,
        ),
        MD5OfBody=str(),
        MD5OfMessageAttributes=str(),
        MessageAttributes={
            "id": {
                "StringValue": "1",
            }
        },
        MessageId=str(),
        ReceiptHandle=str(),
    )

    yield event_failure


@fixture
def event_success() -> Event:
    event_success = Event(
        Body=Parameters(
            seconds=1,
        ),
        MD5OfBody=str(),
        MD5OfMessageAttributes=str(),
        MessageAttributes={
            "id": {
                "StringValue": "2",
            }
        },
        MessageId=str(),
        ReceiptHandle=str(),
    )

    yield event_success


def test_job_processing_failure(
    event_failure: Event,
) -> None:
    try:
        parameters = event_failure.Body
        seconds = parameters.seconds
        timeout = int(getenv("TIMEOUT"))

        event_processing(event_failure)
    except ValueError as value_error:
        error_message = value_error.args[0]

        assert error_message == f"{seconds} major then {timeout}"  # nosec


def test_job_processing_success(
    dynamodb_stub: Stubber,
    event_success: Event,
) -> None:
    with dynamodb_stub:
        event_processing(event_success)
