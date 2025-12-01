# Base image
FROM ros:humble

# Set noninteractive for apt
ENV DEBIAN_FRONTEND=noninteractive

# ----------------------------
# System dependencies
# ----------------------------
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    wget \
    curl \
    vim \
    tmux \
    build-essential \
    cmake \
    locales \
    nano \
    ffmpeg \
    libavdevice-dev \
    libavfilter-dev \
    libavformat-dev \
    libavcodec-dev \
    libswscale-dev \
    libavutil-dev \
    libswresample-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set locale
RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# ----------------------------
# Python & ML Dependencies
# ----------------------------
# Install PyTorch (CPU version; change to CUDA if using GPU)
RUN pip3 install --upgrade pip
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Useful ML packages
RUN pip3 install jupyter matplotlib seaborn numpy pandas tqdm opencv-python

# ----------------------------
# Workspaces
# ----------------------------

# Repo mount point
RUN mkdir -p /root/repo

RUN mkdir -p /root/dev_ws/src/
RUN ln -s /root/repo/ros2_ws/ /root/dev_ws/src/

RUN mkdir -p /root/ml_ws/
RUN ln -s /root/repo/vla/ /root/ml_ws/

# ----------------------------
# Environment variables
# ----------------------------
ENV ROS2_WS=/root/dev_ws
ENV ML_WS=/root/ml_ws
ENV REPO=/root/repo

# Source ROS2 in bash
RUN echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc
RUN echo "export ROS2_WS=/root/dev_ws" >> ~/.bashrc
RUN echo "export ML_WS=/root/ml_ws" >> ~/.bashrc
RUN echo "export REPO=/root/repo" >> ~/.bashrc

# ----------------------------
# Set working directory
# ----------------------------
WORKDIR /root/repo

# Default shell
CMD ["/bin/bash"]
