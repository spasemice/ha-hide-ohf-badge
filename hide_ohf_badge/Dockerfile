FROM ghcr.io/home-assistant/base:latest

RUN apk add --no-cache bash coreutils

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD [ "/run.sh" ]
