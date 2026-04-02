FROM figure1-pro-backend:dev-base

COPY dev/sshd_config /root/
COPY dev/ssh-install.sh /root/

ARG AUTH_KEY

RUN touch /root/.bashrc \
 && echo "export DB_PORT=5432" >> /root/.bashrc

RUN chmod +x /root/ssh-install.sh
RUN /root/ssh-install.sh
