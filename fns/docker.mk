# Makefile for executing fns with docker images

KNATIVE_ENV=${IMAGE_REPO}/knative-${FN}
all:

.PHONY: clean-knative prep-knative run-knative

# Delete a single function:
clean-docker:
	docker ps -q -f name=${FN} | xargs -r docker rm -f

prep-knative-image:
	if ! docker search "${KNATIVE_ENV}" | grep -q "${KNATIVE_ENV}"; then \
	    docker build -t ${KNATIVE_ENV} -f knative.df .; \
	    docker push ${KNATIVE_ENV}; \
	fi

# Pack and register a single function:
prep-docker:
	make clean-docker
	make prep-knative-image
	docker run -d --rm --name ${FN} ${KNATIVE_ENV}

# Run a single function with arguments:
run-docker:
	curl -m '${to}' -X POST -H "Content-Type: application/json" -d "${args}" `docker inspect -f '{{.NetworkSettings.IPAddress}}' ${FN}`:8080
