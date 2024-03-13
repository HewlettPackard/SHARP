# A Docker image to compile reports for benchmarks
# To build, run `docker build --network=host -t reporter .`
FROM rocker/verse:4.2.2

RUN apt-get update
RUN DEBIAN_FRONTEND=noninteractive apt-get install -V -y \
  texlive-binaries \
  texlive-base \
  texlive-font-utils \
  texlive-latex-base \
  texlive-latex-extra \
  texlive-latex-recommended \
  libudunits2-dev \
  libgdal-dev

COPY requirements.R .
RUN Rscript requirements.R
