# AWS Lambda to FastAPI Migration Plan

## Overview
This document outlines the migration plan for converting the AWS Lambda-based API handler (`handler.py`) to a FastAPI application (`main.py`). The migration will maintain all existing functionality while leveraging FastAPI's features for improved developer experience and performance.

## Table of Contents
1. [Project Structure](#project-structure)
2. [Core Components Migration](#core-components-migration)
3. [Authentication Migration](#authentication-migration)
4. [Route Migration](#route-migration)
5. [Database Management](#database-management)
6. [Error Handling](#error-handling)
7. [Configuration Management](#configuration-management)
8. [Dependencies and Requirements](#dependencies-and-requirements)
9. [Testing Strategy](#testing-strategy)
10. [Deployment Considerations](#deployment-considerations)
11. [Migration Steps](#migration-steps)

## Project Structure

### Current Lambda Structure
```
/
├── handler.py          # Main Lambda handler
├── handler_recipes.py  # Recipe-specific handlers
├── handler_ratings.py  # Rating-specific handlers
├── db.py              # Database operations
├── utils.py           # Utility functions
└── template.yaml      # SAM template
```

### Proposed FastAPI Structure
```
/
├── main.py                    # FastAPI application entry point
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── ingredients.py    # Ingredient endpoints
│   │   ├── recipes.py        # Recipe endpoints
│   │   ├── ratings.py        # Rating endpoints
│   │   ├── tags.py          # Tag endpoints
│   │   ├── units.py         # Unit endpoints
│   │   └── auth.py          # Authentication endpoints
│   ├── dependencies/
│   │   ├── __init__.py
│   │   ├── auth.py          # Authentication dependencies
│   │   └── database.py      # Database dependencies
│   └── models/
│       ├── __init__.py
│       ├── requests.py      # Pydantic request models
│       └── responses.py     # Pydantic response models
├── core/
│   ├── __init__.py
│   ├── config.py            # Configuration management
│   ├── database.py          # Database connection/operations
│   └── security.py          # Security utilities
├── utils/
│   ├── __init__.py
│   └── responses.py         # Response utilities
├── requirements.txt         # Python dependencies
└── .env.example            # Environment variables example
```

## Core Components Migration

### 1. Main Application Setup

**Lambda Handler (`handler.py`)**
- Single function handling all routes
- Manual path parsing and method checking
- Global database instance with custom caching

**FastAPI Application (`main.py`)**
- Application factory pattern
- Automatic route registration
- Dependency injection for database connections
- Built-in OpenAPI documentation

### 2. Request/Response Handling

**Lambda**
- Manual JSON parsing from event body
- Custom response formatting functions
- Manual CORS header management

**FastAPI**
- Automatic request parsing with Pydantic models
- Type-safe response models
- CORS middleware configuration

## Authentication Migration

### Current Authentication (Lambda)
- API Gateway Authorizer with Cognito
- Claims extracted from `event['requestContext']['authorizer']['claims']`
- Manual checking for protected routes
- User context passed through function parameters

### Proposed Authentication (FastAPI)
- JWT token validation middleware
- OAuth2 with Password (and Bearer) flow
- Dependency injection for current user
- Route-level authentication decorators

### Implementation Strategy
1. Create JWT validation utilities that verify Cognito tokens
2. Implement OAuth2PasswordBearer for token extraction
3. Create `get_current_user` dependency
4. Add `Depends(get_current_user)` to protected routes
5. Optional: Add role-based access control with dependencies

## Route Migration

### Endpoint Mapping

| Lambda Path | HTTP Method | FastAPI Route | Authentication |
|------------|-------------|---------------|----------------|
| `/ingredients` | GET | `GET /api/v1/ingredients` | Optional |
| `/ingredients` | POST | `POST /api/v1/ingredients` | Required |
| `/ingredients/{id}` | GET | `GET /api/v1/ingredients/{ingredient_id}` | Optional |
| `/ingredients/{id}` | PUT | `PUT /api/v1/ingredients/{ingredient_id}` | Required |
| `/ingredients/{id}` | DELETE | `DELETE /api/v1/ingredients/{ingredient_id}` | Required |
| `/recipes` | GET | `GET /api/v1/recipes` | Optional |
| `/recipes` | POST | `POST /api/v1/recipes` | Required |
| `/recipes/{id}` | GET | `GET /api/v1/recipes/{recipe_id}` | Optional |
| `/recipes/{id}` | PUT | `PUT /api/v1/recipes/{recipe_id}` | Required |
| `/recipes/{id}` | DELETE | `DELETE /api/v1/recipes/{recipe_id}` | Required |
| `/recipes/{id}/public_tags` | POST | `POST /api/v1/recipes/{recipe_id}/public_tags` | Required |
| `/recipes/{id}/public_tags/{tag_id}` | DELETE | `DELETE /api/v1/recipes/{recipe_id}/public_tags/{tag_id}` | Required |
| `/recipes/{id}/private_tags` | POST | `POST /api/v1/recipes/{recipe_id}/private_tags` | Required |
| `/recipes/{id}/private_tags/{tag_id}` | DELETE | `DELETE /api/v1/recipes/{recipe_id}/private_tags/{tag_id}` | Required |
| `/ratings/{recipe_id}` | GET | `GET /api/v1/ratings/{recipe_id}` | Optional |
| `/ratings/{recipe_id}` | POST/PUT | `POST /api/v1/ratings/{recipe_id}` | Required |
| `/ratings/{recipe_id}` | DELETE | `DELETE /api/v1/ratings/{recipe_id}` | Required |
| `/units` | GET | `GET /api/v1/units` | Optional |
| `/auth` | GET | `GET /api/v1/auth/me` | Required |
| `/tags/public` | GET | `GET /api/v1/tags/public` | Optional |
| `/tags/public` | POST | `POST /api/v1/tags/public` | Required |
| `/tags/private` | GET | `GET /api/v1/tags/private` | Required |
| `/tags/private` | POST | `POST /api/v1/tags/private` | Required |

### Query Parameters Migration
- Lambda: `event.get('queryStringParameters', {})`
- FastAPI: Function parameters with Query() validators

### Path Parameters Migration
- Lambda: Manual parsing or `event.get('pathParameters')`
- FastAPI: Function parameters with Path() validators

## Database Management

### Current Approach (Lambda)
- Global database instance with time-based caching
- Manual connection management
- Direct SQL execution in handlers

### Proposed Approach (FastAPI)
- Database connection pool with asyncpg or databases library
- Dependency injection for database sessions
- Repository pattern for database operations
- Optional: SQLAlchemy ORM integration

### Migration Strategy
1. Create database connection factory
2. Implement connection pool configuration
3. Create database dependency for route injection
4. Migrate raw SQL to repository methods
5. Add connection lifecycle management

## Error Handling

### Current Error Handling (Lambda)
- Try-catch blocks in main handler
- Custom error response functions
- Manual status code management

### Proposed Error Handling (FastAPI)
- Global exception handlers
- Custom exception classes
- Automatic status code inference
- Validation error formatting

### Implementation
1. Create custom exception classes
2. Implement global exception handlers
3. Add request validation error formatting
4. Create consistent error response model

## Configuration Management

### Current Configuration (Lambda)
- Environment variables from Lambda configuration
- CloudFormation stack outputs
- Hard-coded fallbacks

### Proposed Configuration (FastAPI)
- Pydantic Settings for configuration
- Environment file support (.env)
- Configuration validation
- Separate configs for different environments

### Configuration Items
- Database connection string
- AWS region
- Cognito User Pool ID
- Cognito App Client ID
- JWT secret/public key
- CORS origins
- API versioning
- Logging configuration

## Dependencies and Requirements

### Core Dependencies
```
fastapi==0.104.1
uvicorn==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
boto3==1.29.0
asyncpg==0.29.0
databases==0.8.0
httpx==0.25.0
pytest==7.4.3
pytest-asyncio==0.21.1
```

### Optional Dependencies
```
sqlalchemy==2.0.23
alembic==1.12.1
redis==5.0.1
celery==5.3.4
sentry-sdk==1.38.0
```

## Testing Strategy

### Unit Tests
1. Test individual route handlers
2. Test authentication/authorization logic
3. Test database repositories
4. Test utility functions

### Integration Tests
1. Test full request/response cycles
2. Test authentication flow
3. Test database transactions
4. Test error scenarios

### Testing Tools
- pytest with pytest-asyncio
- httpx for async client testing
- pytest-mock for mocking
- factory-boy for test data
- coverage.py for code coverage

## Deployment Considerations

### Development Environment
- Use uvicorn for local development
- Hot reload support
- Local PostgreSQL or SQLite
- Mock Cognito for testing

### Production Deployment Options

#### Option 1: Container-based (Recommended)
- Docker container with FastAPI app
- ECS Fargate or EKS deployment
- Application Load Balancer
- Auto-scaling configuration

#### Option 2: Serverless
- AWS Lambda with Mangum adapter
- API Gateway integration
- Keep existing infrastructure
- Minimal changes to deployment

#### Option 3: Traditional Server
- EC2 instances with Gunicorn
- Nginx reverse proxy
- Systemd service management
- Manual scaling

### Infrastructure Requirements
- Load balancer (ALB/NLB)
- Database (RDS PostgreSQL)
- Cache layer (ElastiCache Redis)
- Monitoring (CloudWatch/Datadog)
- Secrets management (AWS Secrets Manager)

## Migration Steps

### Phase 1: Setup and Foundation (Week 1)
1. **Day 1-2**: Create FastAPI project structure
   - Initialize FastAPI application
   - Set up configuration management
   - Create basic health check endpoint
   - Set up logging

2. **Day 3-4**: Database Layer
   - Migrate database connection logic
   - Create database dependency
   - Set up connection pooling
   - Create base repository class

3. **Day 5**: Authentication Framework
   - Implement JWT validation
   - Create authentication dependencies
   - Set up user context management
   - Test with sample protected endpoint

### Phase 2: Route Migration (Week 2-3)
4. **Day 6-7**: Simple GET Endpoints
   - Migrate `/units` endpoint
   - Migrate `/tags/public` GET endpoint
   - Create response models
   - Add basic tests

5. **Day 8-10**: Ingredients Endpoints
   - Create ingredient router
   - Migrate all ingredient CRUD operations
   - Create request/response models
   - Add query parameter handling
   - Write comprehensive tests

6. **Day 11-13**: Recipes Endpoints
   - Create recipe router
   - Migrate recipe CRUD operations
   - Handle complex search functionality
   - Migrate recipe-tag associations
   - Add pagination support

7. **Day 14-15**: Ratings and Tags
   - Migrate rating endpoints
   - Complete tag endpoints (private tags)
   - Handle user-specific operations
   - Add authorization checks

### Phase 3: Testing and Optimization (Week 4)
8. **Day 16-17**: Comprehensive Testing
   - Write missing unit tests
   - Create integration test suite
   - Performance testing
   - Load testing

9. **Day 18-19**: Error Handling and Logging
   - Implement global error handlers
   - Add detailed logging
   - Create monitoring dashboards
   - Add request tracing

10. **Day 20**: Documentation and Cleanup
    - Review and enhance OpenAPI documentation
    - Create deployment documentation
    - Clean up code and remove Lambda artifacts
    - Create migration guide for clients

### Phase 4: Deployment Preparation (Week 5)
11. **Day 21-22**: Container Setup
    - Create Dockerfile
    - Set up docker-compose for local development
    - Create CI/CD pipeline
    - Security scanning

12. **Day 23-24**: Infrastructure as Code
    - Create Terraform/CDK templates
    - Set up staging environment
    - Configure monitoring and alerts
    - Set up secrets management

13. **Day 25**: Final Testing
    - End-to-end testing in staging
    - Performance benchmarking
    - Security audit
    - Rollback procedure testing

### Phase 5: Deployment and Migration (Week 6)
14. **Day 26-27**: Gradual Rollout
    - Deploy to production (canary/blue-green)
    - Monitor metrics and logs
    - Gradual traffic shift
    - Rollback if needed

15. **Day 28-30**: Post-Migration
    - Monitor for issues
    - Performance optimization
    - Documentation updates
    - Team knowledge transfer

## Success Criteria

1. All endpoints functioning identically to Lambda version
2. Authentication working with existing Cognito tokens
3. Performance improvement (response time < 100ms for simple queries)
4. 95%+ test coverage
5. Zero data loss during migration
6. Automatic API documentation available
7. Monitoring and alerting in place
8. Rollback procedure tested and documented

## Risk Mitigation

### Technical Risks
1. **Database connection issues**
   - Mitigation: Extensive connection pool testing
   - Fallback: Keep Lambda version running in parallel

2. **Authentication incompatibility**
   - Mitigation: Thorough testing with production tokens
   - Fallback: Implement compatibility layer

3. **Performance degradation**
   - Mitigation: Load testing and optimization
   - Fallback: Scale infrastructure or revert

### Operational Risks
1. **Deployment failures**
   - Mitigation: Blue-green deployment strategy
   - Fallback: Immediate rollback procedure

2. **Data inconsistency**
   - Mitigation: Read-only mode during migration
   - Fallback: Database backup and restore

## Conclusion

This migration plan provides a structured approach to converting the AWS Lambda-based API to FastAPI. The phased approach allows for incremental progress while maintaining system stability. Each phase builds upon the previous one, with comprehensive testing at each stage to ensure reliability and performance.

The key benefits of this migration include:
- Improved developer experience with FastAPI's automatic documentation
- Better performance through connection pooling and async operations
- Enhanced maintainability with proper separation of concerns
- Easier testing with dependency injection
- More deployment flexibility

Following this plan will result in a modern, scalable, and maintainable API that preserves all existing functionality while providing a foundation for future enhancements. 