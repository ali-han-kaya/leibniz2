const { prepareRuntimeCommand, serverCommand } = require("./runtime");

module.exports = async (kernel) => {
  const port = await kernel.port();
  const url = `http://127.0.0.1:${port}/preview.html`;
  const command = `${prepareRuntimeCommand()} && ${serverCommand(port)}`;

  return {
    daemon: true,
    run: [
      {
        method: "shell.run",
        params: {
          env: {
            PYTHONUNBUFFERED: "1",
          },
          message: [command],
          on: [
            {
              event: "/(http:\\/\\/127\\.0\\.0\\.1:\\d+)/",
              done: true,
            },
          ],
        },
      },
      {
        method: "local.set",
        params: {
          url,
        },
      },
    ],
  };
};
