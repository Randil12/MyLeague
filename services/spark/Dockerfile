FROM spark:3.5.8-java17-python3
USER root
RUN pip3 install --no-cache-dir psycopg2-binary==2.9.13
ADD https://repo.maven.apache.org/maven2/org/postgresql/postgresql/42.7.8/postgresql-42.7.8.jar /opt/spark/jars/postgresql.jar
RUN chmod 644 /opt/spark/jars/postgresql.jar
COPY services/spark/ /opt/myleague/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 185
