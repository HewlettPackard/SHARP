FROM rocker/tidyverse:latest
RUN apt update && apt -y upgrade && apt install -y \
    python3-pip \
    time \
    make \
    llvm \
    g++ \
    git \
    curl \
    rename \
    libopenmpi-dev \
    libgsl-dev \
    libev-dev

RUN R -e 'install.packages(c("shiny", \
                             "shinythemes", \
                             "stringr", \
                             "PearsonDS", \
                             "gsl", \
                             "DT", \
                             "ggdist"))'

RUN git clone https://github.com/hewlettpackard/SHARP
WORKDIR /sharp

RUN pip3 install -r requirements.txt

# Install stragglers, doesn't work otherwise? :/
RUN pip3 install scikit-learn==1.3.2
RUN R -e 'install.packages("shinyFiles")'

EXPOSE 2610

CMD R -e 'shiny::runApp("gui/app.R", port=2610, host = "0.0.0.0")'
