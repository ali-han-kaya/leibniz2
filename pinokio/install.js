const {
  installedMarker,
  prepareRuntimeCommand,
  shellQuote,
} = require("./runtime");

const markInstalled = `printf '%s\\n' 'installed' > ${shellQuote(installedMarker)}`;

module.exports = {
  run: [
    {
      method: "shell.run",
      params: {
        message: [`${prepareRuntimeCommand()} && ${markInstalled}`],
      },
    },
  ],
};
