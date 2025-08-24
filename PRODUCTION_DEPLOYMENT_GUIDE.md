# Production Deployment Guide

## Executive Summary

This guide provides comprehensive procedures for deploying the Musical Bingo application to production following the successful completion of **Phase 1 (Critical Fixes)** and **Phase 2 (Architecture Cleanup)**. The application has been transformed from an emergency state to a production-ready system with enterprise-grade architecture.

## Deployment Readiness Status

### ✅ **PHASE 1 & 2 COMPLETE - PRODUCTION READY**

| Component | Status | Details |
|-----------|--------|---------|
| **Critical Issues** | ✅ RESOLVED | All 4 critical issues (CRIT-001 to HIGH-001) resolved |
| **Architecture** | ✅ OPTIMIZED | Frontend refactored, error handling standardized |
| **Database** | ✅ OPTIMIZED | Constraints, indexes, and performance optimization |
| **Monitoring** | ✅ READY | Comprehensive metrics and health checks |
| **Security** | ✅ HARDENED | Authentication, rate limiting, CSRF protection |
| **Testing** | ✅ COMPREHENSIVE | Test suites for all major components |

## Pre-Deployment Requirements

### Environment Setup

#### Required Environment Variables
```bash
# Security (required)
SECRET_KEY=your_production_secret_key
JWT_SECRET=your_production_jwt_secret  
JWT_REFRESH_SECRET=your_production_jwt_refresh_secret

# Spotify OAuth (required)
SPOTIFY_CLIENT_ID=your_production_client_id
SPOTIFY_CLIENT_SECRET=your_production_client_secret
SPOTIFY_REDIRECT_URI=https://yourdomain.com/auth/callback

# Supabase Database (required)
SUPABASE_URL=your_production_supabase_url
SUPABASE_SERVICE_KEY=your_production_supabase_service_key

# Dragonfly/Redis (required for scaling)
DRAGONFLY_URL=dragonfly://production-redis:6379/0

# Production Settings
ENVIRONMENT=production
LOG_LEVEL=WARNING
CORS_ORIGINS=https://yourdomain.com
```

#### Infrastructure Requirements
- **Python 3.11+** with conda or virtual environment
- **PostgreSQL 15+** (Supabase) with admin access
- **Redis/Dragonfly** for caching and session storage
- **SSL/TLS certificates** for HTTPS
- **Load balancer** (recommended for high availability)

## Database Migration Procedure

### Critical: Run Migrations in Order

**⚠️ IMPORTANT: Create full database backup before starting migrations**

```bash
# 1. Create backup
pg_dump $DATABASE_URL > musical_bingo_backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Run migrations in order
psql $SUPABASE_URL -f supabase/migrations/20250818_add_cascade_delete_constraints.sql
psql $SUPABASE_URL -f supabase/migrations/20250818_add_notifications_table.sql  
psql $SUPABASE_URL -f supabase/migrations/20250824_performance_optimization_indexes.sql

# 3. Verify migrations
psql $SUPABASE_URL -c "SELECT * FROM referential_integrity_status;"
psql $SUPABASE_URL -c "SELECT COUNT(*) FROM notifications;"
```

### Rollback Procedures (If Needed)
```bash
# If issues occur, rollback in reverse order
psql $SUPABASE_URL -f supabase/migrations/rollback_20250818_cascade_delete_constraints.sql
# Restore from backup if necessary
```

## Application Deployment Steps

### Step 1: Pre-Deployment Validation
```bash
# 1. Verify all environment variables
python -c "from app.config import Config; Config.validate_production_config()"

# 2. Run comprehensive test suite  
python tests/run_all_tests.py

# 3. Verify database connections
python -c "from app.database import Database; await Database().health_check()"

# 4. Test Redis/cache connectivity
python -c "from app.cache_manager import get_cache_manager; print(await get_cache_manager().health_check())"
```

### Step 2: Application Deployment
```bash
# 1. Deploy application code
# (Deploy via your preferred method: Docker, systemd, etc.)

# 2. Install dependencies
pip install -r requirements.txt

# 3. Verify startup
python app.py --check-config

# 4. Start services
python app.py
```

### Step 3: Post-Deployment Verification

#### Health Check Endpoints
```bash
# 1. Application health
curl https://yourdomain.com/health
# Expected: {"status": "healthy", "timestamp": "...", "services": {...}}

# 2. Database connectivity
curl https://yourdomain.com/health/database
# Expected: {"database": {"healthy": true, ...}}

# 3. Cache health
curl https://yourdomain.com/health/cache  
# Expected: {"cache": {"healthy": true, ...}}

# 4. Spotify integration
curl https://yourdomain.com/health/spotify
# Expected: {"spotify_config": {"valid": true}}
```

#### Functional Testing
```bash
# 1. Authentication flow
curl -X POST https://yourdomain.com/auth/login

# 2. Game operations  
curl https://yourdomain.com/game/api/games

# 3. Rate limiting (should return 429 after threshold)
# Test rate limiting behavior

# 4. Error handling
curl https://yourdomain.com/api/nonexistent
# Expected: Standardized error response format
```

## Monitoring and Alerting Setup

### Prometheus Metrics (Available Endpoints)
- `/metrics` - Application metrics
- `/health/metrics` - Health check metrics  
- Rate limiting metrics (27+ metrics available)
- Database performance metrics
- Spotify integration metrics

### Log Monitoring
```bash
# Application logs location (configure as needed)
/var/log/musical_bingo/app.log
/var/log/musical_bingo/error.log
/var/log/musical_bingo/security.log
```

### Critical Alerts to Configure
1. **Database Connection Failures**
2. **High Rate Limiting Triggers** (>5% of requests)
3. **Spotify Integration Failures** (>1% failure rate)
4. **Memory/CPU Usage** (>80% sustained)
5. **Error Rate Spikes** (>2% of requests)

## Performance Optimization Configuration

### Redis/Cache Configuration
```python
# Recommended production cache settings
CACHE_CONFIG = {
    "default_ttl": 300,  # 5 minutes
    "max_entries": 10000,
    "cleanup_interval": 600,  # 10 minutes
    "redis_pool_size": 10
}
```

### Rate Limiting Production Settings
```python
# Sustainable production rate limits (already configured)
RATE_LIMITS = {
    "authenticated_user": "120/minute",
    "game_operations": "80/minute", 
    "card_operations": "50/minute",
    "auth_endpoints": "5/minute"
}
```

### Database Connection Pooling
```python
# Recommended database settings
DATABASE_POOL = {
    "min_size": 5,
    "max_size": 20,
    "command_timeout": 30,
    "idle_timeout": 300
}
```

## Security Checklist

### Pre-Deployment Security Verification
- [ ] All secrets properly configured (no defaults)
- [ ] HTTPS enabled with valid SSL certificates  
- [ ] CORS origins restricted to production domain
- [ ] Rate limiting configured and tested
- [ ] CSRF protection enabled
- [ ] Database access properly secured
- [ ] No debug information in production logs
- [ ] Authentication flows tested and secured

## Backup and Recovery Procedures

### Database Backup Strategy
```bash
# Daily automated backups (recommend cron job)
0 2 * * * pg_dump $DATABASE_URL | gzip > /backups/musical_bingo_$(date +\%Y\%m\%d).sql.gz

# Weekly full backup verification
# Monthly restore testing
```

### Application Data Backup
```bash
# User-generated content (saved games, configurations)
cp -r saved_games/ /backups/saved_games_$(date +%Y%m%d)/
```

## Rollback Procedures

### Database Rollback
```bash
# 1. Stop application
systemctl stop musical-bingo

# 2. Restore database
gunzip -c /backups/musical_bingo_YYYYMMDD.sql.gz | psql $DATABASE_URL

# 3. Start application with previous version
systemctl start musical-bingo
```

### Application Rollback
```bash
# 1. Deploy previous version
git checkout [previous-release-tag]

# 2. Restart services  
systemctl restart musical-bingo

# 3. Verify functionality
curl https://yourdomain.com/health
```

## Performance Baseline Expectations

### Expected Performance Metrics
| Metric | Target | Acceptable |
|--------|---------|------------|
| API Response Time | <100ms | <200ms |
| Database Query Time | <50ms | <100ms |
| Memory Usage | <512MB | <1GB |
| CPU Usage | <50% | <75% |
| Cache Hit Rate | >80% | >70% |
| Error Rate | <0.1% | <1% |

### Load Testing Recommendations
```bash
# Test concurrent user load
# Test API rate limiting behavior
# Test database performance under load
# Test WebSocket connections under load
```

## Troubleshooting Guide

### Common Issues and Solutions

#### High Memory Usage
```bash
# Check for memory leaks
ps aux | grep python
# Monitor cache usage
curl https://yourdomain.com/health/cache
```

#### Database Connection Issues  
```bash
# Check database connectivity
psql $SUPABASE_URL -c "SELECT 1;"
# Review connection pool settings
```

#### Rate Limiting Issues
```bash
# Check rate limiting metrics
curl https://yourdomain.com/metrics | grep rate_limit
# Review rate limiting logs
```

#### Spotify Integration Failures
```bash
# Check token management health
curl https://yourdomain.com/token/health/service
# Review background service status  
```

## Post-Deployment Monitoring

### Week 1: Intensive Monitoring
- [ ] Monitor all health endpoints hourly
- [ ] Review error logs daily
- [ ] Track performance metrics continuously
- [ ] Monitor user feedback and issues
- [ ] Validate backup procedures

### Week 2-4: Standard Monitoring
- [ ] Daily health check reviews
- [ ] Weekly performance analysis
- [ ] Monthly security reviews
- [ ] Quarterly load testing

### Ongoing Maintenance
- [ ] Regular dependency updates
- [ ] Security patch management  
- [ ] Performance optimization reviews
- [ ] User feedback integration
- [ ] Feature enhancement planning

## Support and Escalation

### Production Issue Severity Levels

**P0 - Critical (< 15 min response)**
- Application completely down
- Database connectivity lost
- Security breach detected

**P1 - High (< 1 hour response)**  
- Major functionality broken
- Performance severely degraded
- Authentication failures

**P2 - Medium (< 4 hours response)**
- Minor functionality issues
- Non-critical errors
- Performance concerns

**P3 - Low (< 24 hours response)**
- Enhancement requests
- Documentation updates
- Minor improvements

## Success Criteria

### Production Deployment Success Metrics
- [ ] Application starts successfully
- [ ] All health checks pass
- [ ] Database migrations completed
- [ ] Authentication flows work
- [ ] Spotify integration functional
- [ ] Performance within targets
- [ ] Error rates acceptable
- [ ] User acceptance testing passed

---

**Deployment Readiness:** ✅ READY FOR PRODUCTION  
**Risk Level:** LOW (Comprehensive testing and rollback procedures)  
**Expected Downtime:** < 15 minutes (for migrations)  
**Monitoring Period:** 4 weeks intensive, then standard monitoring

*Document Version: 1.0*  
*Last Updated: 2025-08-18*  
*Next Review: Post-deployment (1 week)*