FROM rocker/tidyverse:4.3
RUN apt update && apt -y upgrade && apt install -y \
    python3-pip \
    time \
    make \
    llvm \
    g++ \
    curl \
    rename \
    libopenmpi-dev \
    libgsl-dev \
    libev-dev \
    libharfbuzz-dev \
    libfribidi-dev

RUN R -e 'install.packages(c("shiny", \
                             "shinybusy", \
                             "shinythemes", \
                             "ShinyFiles", \
                             "tidyverse", \
                             "stringr", \
                             "PearsonDS", \
                             "LaplacesDemon", \
                             "moments", \
                             "processx", \
                             "rpart", \
                             "regclass", \
                             "sparkline", \
                             "visNetwork", \
                             "fansi", \
                             "yaml", \
                             "gsl", \
                             "DT", \
                             "ggdist", \
                             "GGally"))'

# To be replaced with git clone:
COPY requirements.txt .
RUN pip3 install --break-system-packages --ignore-installed -r requirements.txt

# Install stragglers, doesn't work otherwise? :/
RUN pip3 install scikit-learn==1.3.2
RUN R -e 'install.packages("shinyFiles")'

# To be replaced with git clone:
COPY . /usr/sharp

EXPOSE 2626

CMD R -e 'shiny::runApp("/usr/sharp/gui/app.R", port=2626, host = "0.0.0.0")'
# CMD R -e 'shiny::runApp("/demo/app.R", port=2626, host = "0.0.0.0")'
