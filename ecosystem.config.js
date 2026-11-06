module.exports = {
  apps: [
    {
      name: 'make-ai-service-pipl',
      script: 'server.py',
      interpreter: '.venv/bin/python',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        PORT: 4006,
        INSTANCE_NAME: 'PIPL'
      }
    },
    {
      name: 'make-ai-service-ndcs',
      script: 'server.py',
      interpreter: '.venv/bin/python',
      instances: 1,
      exec_mode: 'fork',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      env: {
        PORT: 4008,
        INSTANCE_NAME: 'NDCS'
      }
    }
  ]
};
