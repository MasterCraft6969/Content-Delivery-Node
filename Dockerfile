# Dockerfile

FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential git

RUN cd /app 

RUN git clone https://github.com/MasterCraft6969/Content-Delivery-Node/ .

RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends nano && addgroup --system appgroup && adduser --system --ingroup appgroup user

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

COPY --from=builder --chown=user:appgroup /app /app

RUN chown -R user:appgroup /app

RUN chmod +x /app/start.sh

USER user

EXPOSE 5000

CMD ["/bin/bash"]