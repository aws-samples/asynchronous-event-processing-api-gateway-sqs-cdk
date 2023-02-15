from aws_lambda_powertools.utilities.typing import (
    LambdaContext,
)
from aws_lambda_powertools import (
    Logger,
)
from boto3 import (
    client,
)
from json import (
    dumps,
)
from os import (
    getenv,
)

TABLE_NAME = getenv("TABLE_NAME")
dynamodb = client("dynamodb")
logger = Logger(
    level=getenv("LOG_LEVEL", "INFO"),
    service="error_handling",
)


def handler(event: dict, context: LambdaContext) -> None:
    logger.debug(event)

    for record in event["Records"]:
        body = record["body"]
        id = record["messageAttributes"]["id"]["stringValue"]

        dynamodb.put_item(
            Item={
                "id": {
                    "S": id,
                },
                "parameters": {
                    "S": dumps(body),
                },
                "status": {
                    "S": "Failure",
                },
            },
            TableName=TABLE_NAME,
        )
