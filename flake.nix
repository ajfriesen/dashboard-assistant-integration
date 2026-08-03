{
  description = "Dashboard Assistant Home Assistant integration — dev shell";

  inputs = {
    # Same channel the OS repo pins, so both dev shells resolve from one store.
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  };

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = [
          # Conventional Commits tooling: `cz commit` for a guided message,
          # `cz check` to lint one. Versioning/changelog itself is handled by
          # release-please in CI (see .github/workflows/release-please.yml); this
          # is purely to author and validate the commit messages it reads.
          pkgs.commitizen
        ];

        # Point git at the version-controlled hook (.githooks/commit-msg) so every
        # commit is checked against Conventional Commits locally, not just PRs in
        # CI. Idempotent — safe to re-run on each shell entry.
        shellHook = ''
          if [ -d .git ]; then
            git config core.hooksPath .githooks
          fi
          echo "commitizen ready — 'cz commit' for a guided message, 'cz check' to lint."
        '';
      };

      formatter.${system} = pkgs.nixfmt;
    };
}
