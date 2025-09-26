# Makefile for executing fns with docker images

DOCKER_ENV=${IMAGE_REPO}/docker-${FN}
all:

.PHONY: clean-docker prep-docker run-docker

# Delete a single function:
clean-docker:
	docker ps -q -f name=${FN} | xargs -r docker rm -f

prep-docker-image:
	if ! docker search "${DOCKER_ENV}" | grep -q "${DOCKER_ENV}"; then \
		docker build -t ${DOCKER_ENV} -f docker.df .; \
		docker push ${DOCKER_ENV}; \
	fi

# Pack and register a single function:
prep-docker:
	make clean-docker
	make prep-docker-image
	docker run -d --rm --name ${FN} ${DOCKER_ENV}

# Run a single function with arguments:
run-docker:
	docker exec ${FN} python3 ${FN}.py "${args}"
