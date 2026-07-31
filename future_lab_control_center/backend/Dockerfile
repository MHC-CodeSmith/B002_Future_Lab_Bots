# ============================================================
# Dockerfile — Backend FastAPI + ROS 2 (Future Lab Control Center)
# ============================================================
FROM ros:jazzy-ros-base

WORKDIR /app

# Instala pip, ferramentas de rede, SSH, OpenGL e bibliotecas ROS 2
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    iputils-ping \
    curl \
    sshpass \
    openssh-client \
    docker.io \
    x11-xserver-utils \
    libgl1 \
    libglib2.0-0 \
    ros-jazzy-cyclonedds \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-rmw-fastrtps-cpp \
    ros-jazzy-moveit-msgs \
    ros-jazzy-control-msgs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --break-system-packages --ignore-installed -r /app/requirements.txt

COPY . /app/backend

ENV PYTHONPATH=/app
ENV ROS_DOMAIN_ID=42
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

EXPOSE 8000

# Executa o backend com o ambiente do ROS 2 Jazzy ativado
CMD ["bash", "-c", "source /opt/ros/jazzy/setup.bash && python3 /app/backend/main.py"]
