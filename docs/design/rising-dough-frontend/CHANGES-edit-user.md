# Update · Edit user (ST17)

Copy these files over your `rising-dough-frontend/` folder. They replace the files with the same paths.

New
- `pages/overlays/edit-user.html`: the Edit user dialog (460px). The email is fixed and read-only; name and
  member/admin can be changed; `[ save ]`. In the app it's an `hx-get` into `#modal-root` and a POST that swaps the
  user row and adds `flash/success`.

Changed
- `pages/settings/users.html`: *edit user* is the first item in a member's row menu, before reset password and
  delete user. The owner's own row still has no menu, so an admin can't demote or delete themselves.
- The 8 other Users overlays (`add-user`, `add-user--error`, `one-time-password`, `reset-password`,
  `delete-user`, `invite-user`, `invite-user--error`, `revoke-invite`) show the Users page underneath, so their
  copy of the row menu gains the same item.
- `index.html` lists the new overlay. `README.md` has it in "What changed in this update".
- CSS: the read-only field style (`.rd-field--readonly`, raised fill, muted text) moved from
  `pages/auth.css` to `components/field.css`, because a dialog uses it now as well as the invite page. It looks the
  same as before.

No JS, token or other page changes.
