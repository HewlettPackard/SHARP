# Makefile for GSL integration benchmark
# Requires: libgsl-dev (apt install libgsl-dev)

CC = gcc
CFLAGS = -O2 -Wall -Wextra
LDFLAGS = -lgsl -lgslcblas -lm

TARGET = gsl_integrate
SRC = gsl_integrate.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f $(TARGET)

test: $(TARGET)
	./$(TARGET) 10

.PHONY: all clean test
