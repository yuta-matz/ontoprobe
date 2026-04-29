{
  description = "Python project devshell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            python312  # .python-version に合わせて 3.12 を使用
            uv
            ruff
          ];

          # uv が venv を作る場所を固定
          env = {
            UV_PYTHON_DOWNLOADS = "never";  # nixpkgs の python を使う
          };

          shellHook = ''
            # venv 自動作成 (.venv が無ければ)
            if [ ! -d .venv ]; then
              uv venv --python "$(which python3)" .venv
            fi
            # venv 自動有効化
            source .venv/bin/activate
            # uv に nix の python を使わせる
            export UV_PYTHON="$(which python3)"
          '';
        };
      });
}
