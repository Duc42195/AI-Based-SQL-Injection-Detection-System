FROM sqli-detection:latest

USER root
COPY docker/vuln_app/app.py /app/
ENV VIRTUAL_ENV=/app/.venv
ENV PATH=/app/.venv/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN uv pip install flask psycopg2-binary --quiet

EXPOSE 42801
CMD ["python", "app.py"]
