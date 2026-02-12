{
  description = "MediaTamer (organize + extract MKV metadata)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in
    {

      packages."${system}".default = pkgs.python3Packages.buildPythonPackage rec {
        pname = "mediatamer";
        version = "0.1.0";
        src = ./.;
        nativeBuildInputs = [
          pkgs.python3
          pkgs.python3Packages.setuptools
          pkgs.python3Packages.wheel
        ];
        buildInputs = [ pkgs.ffmpeg ];
        pyproject = true;
        meta = with pkgs.lib; {
          description = "MediaTamer — organize media and extract MKV metadata";
          license = licenses.mit;
        };
      };

      devShells."${system}".default = pkgs.mkShell {
        name = "mediatamer-dev";
        packages = [
          self.packages."${system}".default
        ];
      };

      defaultPackage = self.packages."${system}".default;
    };
}
