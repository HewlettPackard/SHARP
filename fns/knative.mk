# Makefile for numpy-based matrix multiplication

KNATIVE_ENV=${IMAGE_REPO}/knative-${FN}
all:

.PHONY: clean-knative prep-knative run-knative

# Delete a single function:
clean-knative:
	if [ "$$(kubectl get ksvc | \
		awk '$$1 == "NAME" {next} $$1 == "${FN}" {print "true"; exit}')" = "true" ]; \
	then \
		kubectl delete ksvc ${FN} ; \
	fi

prep-knative-image:
	if ! docker search "${KNATIVE_ENV}" | grep -q "${KNATIVE_ENV}"; then \
		docker build -t ${KNATIVE_ENV} -f knative.df .; \
		docker push ${KNATIVE_ENV}; \
	fi
 
# Pack and register a single function:
prep-knative:
	make clean-knative
	make prep-knative-image
	echo "apiVersion: serving.knative.dev/v1\nkind: Service\nmetadata:\n  name: ${FN}\nspec:\n  template:\n    spec:\n      containers:\n        - image: ${KNATIVE_ENV}" | kubectl apply -f -

# Run a single function with arguments:
run-knative:
	curl -m '${to}' -X POST -H "Content-Type: application/json" -d "${args}" `kubectl get ksvc ${FN} -o jsonpath='{.status.url}'`
