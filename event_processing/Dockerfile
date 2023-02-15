FROM python:3.9

RUN useradd -ms /bin/bash python
USER python
WORKDIR /home/python

COPY main.py requirements.txt ./
RUN pip install -r requirements.txt
RUN rm -f requirements.txt

HEALTHCHECK NONE

CMD [ "python", "./main.py" ]
