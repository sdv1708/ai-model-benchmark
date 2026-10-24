import { execFileSync } from 'node:child_process'
import path from 'node:path'
import { backendDirectory, backendPython } from './runtime'

export default function globalSetup() {
  execFileSync(backendPython, [path.join(import.meta.dirname, 'generate_browser_fixtures.py')], {
    stdio: 'inherit',
  })
  // Verify the API fixture export path too; browser tests upload these exact bytes.
  execFileSync(backendPython, [path.join(backendDirectory, 'tests/resilience_fixtures.py')], {
    stdio: 'inherit',
  })
}
