module.exports = {
    apps: [
        {
            name: "corniche-bot",
            script: "src/main.py",
            interpreter: "venv/bin/python3",
            watch: false,
            autorestart: true,
            max_memory_restart: '500M',
            env: {
                NODE_ENV: "production",
            }
        },
        {
            name: "corniche-dashboard",
            script: "venv/bin/python3",
            args: "-m streamlit run src/dashboard.py --server.port 8501",
            interpreter: "none",
            watch: false,
            autorestart: true,
            env: {
                NODE_ENV: "production",
            }
        }
    ]
};
