FROM python:latest

WORKDIR /usr/src/somosapp

EXPOSE 8000

RUN apt-get update
RUN apt-get -y upgrade

COPY . .
RUN pip3 install --upgrade pip
RUN apt-get -y install vim
RUN apt update -y
RUN apt-get install -y python-dev default-libmysqlclient-dev && pip install mysqlclient
RUN pip install -r requirements.txt
CMD ["uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]