FROM python:3
WORKDIR /measurement
COPY . .
RUN apt-get update
RUN pip3 install kubernetes
RUN pip3 install numpy
RUN pip3 install redis
CMD python3 latency_measurement.py
