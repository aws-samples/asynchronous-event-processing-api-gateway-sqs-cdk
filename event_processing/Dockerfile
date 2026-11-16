FROM public.ecr.aws/amazonlinux/amazonlinux:2023

RUN dnf install -y python3 python3-pip shadow-utils && dnf clean all

RUN useradd -ms /bin/bash python
USER python
WORKDIR /home/python

COPY main.py requirements.txt ./
RUN pip3 install -r requirements.txt
RUN rm -f requirements.txt

HEALTHCHECK NONE

CMD [ "python3", "./main.py" ]
