FROM python:3.6-buster

WORKDIR /src/thunderstorm_library

COPY . .

RUN pip install --pre -e ".[kafka]"
RUN pip install -r requirements-dev.txt

CMD "pytest -s test"
