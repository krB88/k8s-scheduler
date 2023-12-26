FROM python:3
WORKDIR /scheduler
COPY . .
RUN apt-get update
RUN pip3 install kubernetes
RUN pip3 install numpy
RUN pip3 install redis
CMD python3 scheduler.py
