from aws_lambda_powertools import (
    Logger,
)
from aws_lambda_powertools.utilities.parser import (
    BaseModel,
    parse,
)
from boto3 import (
    client,
    resource,
)
from json import (
    loads,
)
from os import (
    getenv,
)
from time import (
    sleep,
)


class Id(BaseModel):
    StringValue: str


class MsgAttrs(BaseModel):
    id: Id


class Parameters(BaseModel):
    seconds: int


class Event(BaseModel):
    Body: Parameters
    MD5OfBody: str
    MD5OfMessageAttributes: str
    MessageAttributes: MsgAttrs
    MessageId: str
    ReceiptHandle: str


QUEUE_NAME = getenv("QUEUE_NAME")
TABLE_NAME = getenv("TABLE_NAME")
TIMEOUT = int(getenv("TIMEOUT"))
dynamodb = client("dynamodb")
logger = Logger(
    level=getenv("LOG_LEVEL", "INFO"),
    service="event_processing",
)
sqs_client = client("sqs")
sqs_resource = resource("sqs")


def event_processing(event: Event) -> None:
    logger.debug(event)

    event = parse(event=event, model=Event)
    id = event.MessageAttributes.id.StringValue
    parameters = event.Body
    seconds = parameters.seconds
    message = f"I slept for {seconds} seconds"

    if seconds > TIMEOUT:
        raise ValueError(f"{seconds} major then {TIMEOUT}")

    sleep(seconds)

    results = f"{{\"message\": \"{message}\"}}"

    dynamodb.put_item(
        Item={
            "id": {
                "S": id,
            },
            "results": {
                "S": results,
            },
            "status": {
                "S": "Success",
            },
        },
        TableName=TABLE_NAME,
    )


if __name__ == "__main__":
    while True:
        try:
            jobs_queue = sqs_resource.get_queue_by_name(QueueName=QUEUE_NAME)
            jobs_queue_url = jobs_queue.url
            response = sqs_client.receive_message(
                MaxNumberOfMessages=10,
                MessageAttributeNames=["All"],
                QueueUrl=jobs_queue_url,
            )

            for message in response.get("Messages", []):
                id = message["MessageAttributes"]["id"]["StringValue"]
                message["Body"] = loads(message["Body"])

                event_processing(message)
                sqs_client.delete_message(
                    QueueUrl=jobs_queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
        except Exception as exception:
            logger.error((f"Message {id} processing failed "
                          f"with exception: {exception}"))
