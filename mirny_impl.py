import argparse

def get_argparser():
    parser = argparse.ArgumentParser(
        description="Mirny CPLD firmware"
    )
    parser.add_argument("--legacy-almazny", action="store_true", default=False)

    return parser

def main():
    from mirny_cpld import Platform
    from mirny import Mirny

    parsed = get_argparser().parse_args()

    p = Platform()
    mirny = Mirny(p, parsed.legacy_almazny)
    p.build(mirny, build_name="mirny", mode="cpld")


if __name__ == "__main__":
    main()
