FROM public.ecr.aws/lambda/python:3.12

# Layer 1: Install barcart dependencies (heavy, rarely change)
COPY ../packages/barcart/requirements.txt /tmp/barcart-requirements.txt
RUN pip install --no-cache-dir -r /tmp/barcart-requirements.txt

# Layer 2: Install analytics dependencies (rarely change)
COPY analytics/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Layer 3: Copy shared modules (change occasionally)
COPY db/ ${LAMBDA_TASK_ROOT}/db/
COPY utils/ ${LAMBDA_TASK_ROOT}/utils/
COPY core/ ${LAMBDA_TASK_ROOT}/core/

# Layer 4: Install barcart package code (changes frequently)
COPY ../packages/barcart/ ${LAMBDA_TASK_ROOT}/packages/barcart/
RUN pip install --no-deps ${LAMBDA_TASK_ROOT}/packages/barcart/

# Layer 5: Copy analytics function code (changes frequently)
COPY analytics/analytics_refresh.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD [ "analytics_refresh.lambda_handler" ]
