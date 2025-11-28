FROM public.ecr.aws/lambda/python:3.12

# Copy requirements first for better caching
COPY analytics/requirements.txt ${LAMBDA_TASK_ROOT}/

# Install dependencies
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy shared modules from parent api/ directory
COPY db/ ${LAMBDA_TASK_ROOT}/db/
COPY utils/ ${LAMBDA_TASK_ROOT}/utils/
COPY core/ ${LAMBDA_TASK_ROOT}/core/

# Copy analytics function code
COPY analytics/analytics_refresh.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD [ "analytics_refresh.lambda_handler" ]
