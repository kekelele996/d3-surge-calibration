# 基础镜像按补丁版本 + digest 双重锁定。
FROM python:3.12.7-slim-bookworm@sha256:60d9996b6a8a3689d36db740b49f4327be3be09a21122bd02fb8895abb38b50d

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 解题与参考解身份由 task.toml 的 [agent] user = "runner" 指定。
# 不写 USER：Harbor 保活进程随默认用户运行，评分前清理 runner 进程时不能误杀。
RUN useradd --create-home --uid 1000 runner

WORKDIR /app
COPY app/ /app/
COPY cases/ /app/cases/
RUN chown -R runner:runner /app
