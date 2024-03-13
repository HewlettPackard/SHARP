# Makefile for numpy-based matrix multiplication
FISSION_ENV_PATH=${IMAGE_REPO}/${FISSION_ENV}
all:

.PHONY: clean-fission prep-fission-image prep-fission-env prep-fission run-fission

# Delete a single function:
clean-fission:
	${FBIN} fn delete --name ${FN} --ignorenotfound=true
	${FBIN} pkg list | awk '$$1 == "NAME" {next} $$1 ~ /^${FN}/ {print $$1}' | xargs -I {} fission pkg delete --name {}

prep-fission-image:
	if ! docker search "${FISSION_ENV_PATH}" | grep -q "${FISSION_ENV_PATH}"; then \
	docker build -t ${FISSION_ENV_PATH} -f fission.df .; \
	docker push ${FISSION_ENV_PATH}; \
	fi

prep-fission-env:
	# If not exists, create a Fission environment:
	if [ "$$(fission env list | \
        awk '$$1 == "NAME" {next} $$1 == "${FISSION_ENV}" {print "true"; exit}')" != "true" ]; \
    then \
		fission env create --name ${FISSION_ENV} \
    	  --image $(FISSION_ENV_PATH) \
    	  --mincpu 40 --maxcpu 48000 \
    	  --minmemory 64 --maxmemory 168000 \
    	  --poolsize 1; \
	fi
 
# Pack and register a single function:
prep-fission:
	make clean-fission
	make prep-fission-image
	make prep-fission-env
	#cd .. ; zip -jr ${ZIP} ${FN}/ ; cd -
	#${FBIN} package create --name ${PKG} --sourcearchive ../${ZIP} --env ${ENV} --buildcmd "./build-fission.sh"
	#until fission pkg info --name "${PKG}" | awk 'NR==3' | grep -q "succeeded"; do \
	#	echo -n "." && sleep 1; \
	#	if fission pkg info --name "${PKG}" | awk 'NR==3' | grep -q "failed"; then \
	#		echo "package ${PKG} failed to build"; \
	#		fission pkg info --name "${PKG}"; \
	#		fission pkg delete --name "${PKG}"; \
	#	fi; \
	#done
	${FBIN} fn create --name ${FN} --env ${FISSION_ENV} --code ${FN}.py

# Run a single function with arguments:
run-fission:
	${FBIN} fn test --name ${FN} -t ${to}s -b "${args}"

clean-fission-env:
	${FBIN} env delete --name ${FISSION_ENV} --ignorenotfound=true
