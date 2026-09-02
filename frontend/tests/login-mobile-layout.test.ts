import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const loginViewSource = readFileSync(
  join(process.cwd(), 'src', 'views', 'LoginView.vue'),
  'utf8',
)

const mobileMediaMatch = loginViewSource.match(
  /@media \(max-width: 900px\) \{(?<body>[\s\S]*?)\n\}/,
)

test('mobile login page is a bounded scroll container so bottom actions stay reachable', () => {
  assert.ok(mobileMediaMatch?.groups?.body, 'expected max-width 900px mobile styles')
  const mobileStyles = mobileMediaMatch.groups.body

  assert.match(
    mobileStyles,
    /\.login-page\s*\{[\s\S]*(?:^|\n)\s*height:\s*100dvh;/,
  )
  assert.match(
    mobileStyles,
    /\.login-page\s*\{[\s\S]*overflow-y:\s*auto;/,
  )
  assert.doesNotMatch(mobileStyles, /\.login-page\s*\{[\s\S]*(?:^|\n)\s*height:\s*auto;/)
})
