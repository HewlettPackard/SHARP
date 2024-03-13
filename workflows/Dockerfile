FROM python:3.10

RUN pip3 install pyyaml requests jsonschema
RUN git clone https://github.com/serverlessworkflow/sdk-python
WORKDIR sdk-python
RUN python3 setup.py build
COPY validator.py .
