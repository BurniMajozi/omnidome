/* eslint-disable @typescript-eslint/no-require-imports */

const path = require("path")

process.env.NODE_ENV = "development"

const { startServer } = require("next/dist/server/lib/start-server")

const port = process.env.PORT ? Number(process.env.PORT) : 3000
const hostname = process.env.HOSTNAME || undefined

startServer({
    dir: path.resolve(__dirname, ".."),
    port,
    allowRetry: true,
    isDev: true,
    hostname
}).catch((err) => {
    console.error(err)
    process.exit(1)
})
