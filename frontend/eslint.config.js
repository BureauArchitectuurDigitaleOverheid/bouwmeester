import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import globals from 'globals'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Disable overly strict new react-hooks rules that trigger on existing patterns
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      'react-refresh/only-export-components': [
        'warn',
        {
          allowConstantExport: true,
          allowExportNames: [
            'useAuth',
            'useCurrentPerson',
            'useNodeDetail',
            'useTaskDetail',
            'useVocabulary',
          ],
        },
      ],
      // Allow unused vars with underscore prefix
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // A boolean expression passed straight to a boolean attribute of an
      // nldd-* custom element. React renders `false` as the literal attribute
      // `checked="false"`, and a custom element reads mere presence as true —
      // so `checked={false}` turns the thing ON. It fails silently and in the
      // wrong direction, and it caught seven call sites during the migration.
      //
      // Write `checked={orUndef(x)}` (from components/nldd/events) instead.
      // Our own React wrappers (NlddButton, Badge, ...) already guard
      // internally, so this only targets the raw elements.
      'no-restricted-syntax': [
        'error',
        {
          selector:
            'JSXElement[openingElement.name.name=/^nldd-/] > JSXOpeningElement >' +
            // `current` is left out on purpose: nldd-pagination uses it for a
            // page NUMBER, so it is not always a boolean.
            ' JSXAttribute[name.name=/^(checked|selected|expanded|invalid|valid|disabled|required|loading|pulse|reorderable|button|checkbox|radio|optional|judging|hint|annotatable|box|wrap|single-line|no-tab)$/]' +
            ' > JSXExpressionContainer >' +
            ' :matches(Identifier, MemberExpression, UnaryExpression, BinaryExpression, LogicalExpression)',
          message:
            'Boolean attributes on nldd-* elements must be `true | undefined`, never `false`: ' +
            'React writes `false` as the attribute "false" and the element reads presence as true. ' +
            'Wrap it: checked={orUndef(x)} — see src/components/nldd/events.ts.',
        },
      ],
    },
  },
)
