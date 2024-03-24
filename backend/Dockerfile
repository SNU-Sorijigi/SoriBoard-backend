FROM python:3.12
ENV PYTHONUNBUFFERED 1

RUN mkdir -p /docker-server/soriboard_backend
WORKDIR /docker-server/soriboard_backend
ADD . /docker-server/soriboard_backend

RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN python manage.py makemigrations
RUN python manage.py migrate

EXPOSE 8080

CMD ["daphne", "-b", "0.0.0.0", "-p", "8080", "asgi:application"]
